import os
import zipfile

from rest_framework import serializers
from .models import (
    Barangay,
    DeathRecord,
    Document,
    FamilyMember,
    GroceryClaim,
    PensionRecord,
    ResidenceTransferRecord,
    SeniorCitizen,
)

class BarangaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Barangay
        fields = ["id", "code", "name", "municipality"]


class FamilyMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = FamilyMember
        fields = ["name", "relation", "age", "occupation"]


class SeniorCitizenSerializer(serializers.ModelSerializer):
    barangay = serializers.PrimaryKeyRelatedField(
        queryset=Barangay.objects.filter(is_active=True),
        allow_null=False,
        required=True,
    )
    age = serializers.IntegerField(read_only=True)
    barangay_name = serializers.CharField(
        source="barangay.name",
        read_only=True,
        allow_null=True,
    )
    family_members = FamilyMemberSerializer(many=True, required=False, write_only=True)

    class Meta:
        model = SeniorCitizen
        fields = [
            "id",
            "osca_id",
            "registration_cert_no",
            "first_name",
            "middle_name",
            "suffix",
            "last_name",
            "date_of_birth",
            "date_of_registration",
            "age",
            "sex",
            "civil_status",
            "address",
            "barangay",
            "barangay_name",
            "latitude",
            "longitude",
            "place_of_birth",
            "educational_attainment",
            "occupation",
            "annual_income",
            "other_skills",
            "association_name",
            "association_address",
            "is_association_member",
            "date_of_membership",
            "position",
            "family_members",
            "has_portal_account",
            "milestone_age",
            "registration_status",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["osca_id", "registration_cert_no", "date_of_registration", "created_at"]

    has_portal_account = serializers.SerializerMethodField()

    def get_has_portal_account(self, obj):
        return obj.portal_users.exists()

    def validate(self, attrs):
        from django.utils import timezone

        date_of_birth = attrs.get("date_of_birth", getattr(self.instance, "date_of_birth", None))
        if date_of_birth:
            today = timezone.localdate()
            if date_of_birth > today:
                raise serializers.ValidationError({"date_of_birth": "Date of birth cannot be in the future."})
            age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
            if age < 60:
                raise serializers.ValidationError({"date_of_birth": "Senior citizen must be at least 60 years old."})
            attrs["age"] = age

        request = self.context.get("request")
        if request and request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile:
                raise serializers.ValidationError("This staff account has no assigned barangay.")
            if "barangay" in attrs and attrs["barangay"].id != profile.barangay_id:
                raise serializers.ValidationError({"barangay": "You cannot move a senior citizen to another barangay."})
        return attrs

    def create(self, validated_data):
        family_members = validated_data.pop("family_members", [])
        senior = super().create(validated_data)
        FamilyMember.objects.bulk_create([
            FamilyMember(senior_citizen=senior, **item)
            for item in family_members
            if item.get("name", "").strip()
        ])
        return senior

    def update(self, instance, validated_data):
        family_members = validated_data.pop("family_members", None)
        senior = super().update(instance, validated_data)
        if family_members is not None:
            senior.family_members.all().delete()
            FamilyMember.objects.bulk_create([
                FamilyMember(senior_citizen=senior, **item)
                for item in family_members
                if item.get("name", "").strip()
            ])
        return senior


class DocumentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    senior_name = serializers.SerializerMethodField()
    senior_osca_id = serializers.CharField(source="senior_citizen.osca_id", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id", "senior_citizen", "senior_name", "senior_osca_id",
            "document_type", "file", "file_name", "upload_date",
            "nlp_classification", "nlp_confidence", "classifier_source", "extracted_entities",
            "is_verified", "review_status", "review_note", "reviewed_by",
            "reviewed_at", "created_at",
        ]
        read_only_fields = [
            "file_name", "upload_date", "nlp_classification", "nlp_confidence", "classifier_source",
            "extracted_entities", "is_verified", "review_status", "review_note",
            "reviewed_by", "reviewed_at", "created_at",
        ]

    reviewed_by = serializers.CharField(source="reviewed_by.username", read_only=True, allow_null=True)

    def get_senior_name(self, obj):
        return f"{obj.senior_citizen.first_name} {obj.senior_citizen.last_name}".strip()

    def validate_file(self, uploaded_file):
        allowed_extensions = {".pdf", ".docx", ".jpg", ".jpeg", ".png"}
        extension = os.path.splitext(uploaded_file.name)[1].lower()
        if extension not in allowed_extensions:
            raise serializers.ValidationError("Use a PDF, DOCX, JPG, JPEG, or PNG file.")
        if uploaded_file.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Each file must be 10 MB or smaller.")
        uploaded_file.seek(0)
        signature = uploaded_file.read(16)
        uploaded_file.seek(0)
        signatures = {
            ".pdf": signature.startswith(b"%PDF-"),
            ".jpg": signature.startswith(b"\xff\xd8\xff"),
            ".jpeg": signature.startswith(b"\xff\xd8\xff"),
            ".png": signature.startswith(b"\x89PNG\r\n\x1a\n"),
            ".docx": signature.startswith(b"PK\x03\x04"),
        }
        if not signatures.get(extension, False):
            raise serializers.ValidationError("The file contents do not match its extension or the file is empty.")
        if extension in {".jpg", ".jpeg", ".png"}:
            try:
                from PIL import Image

                with Image.open(uploaded_file) as image:
                    image.verify()
            except ImportError:
                pass
            except Exception:
                raise serializers.ValidationError("The image file is damaged or invalid.")
            finally:
                uploaded_file.seek(0)
        if extension == ".pdf":
            try:
                uploaded_file.seek(max(0, uploaded_file.size - 2048))
                if b"%%EOF" not in uploaded_file.read():
                    raise serializers.ValidationError("The PDF file is incomplete or invalid.")
                uploaded_file.seek(0)
                try:
                    from pypdf import PdfReader

                    pdf = PdfReader(uploaded_file, strict=True)
                    if not pdf.pages or len(pdf.pages) > 100:
                        raise serializers.ValidationError("PDF files must contain between 1 and 100 pages.")
                except ImportError:
                    pass
                except serializers.ValidationError:
                    raise
                except Exception:
                    raise serializers.ValidationError("The PDF file is damaged, encrypted, or invalid.")
            finally:
                uploaded_file.seek(0)
        if extension == ".docx":
            try:
                with zipfile.ZipFile(uploaded_file) as archive:
                    if "word/document.xml" not in archive.namelist():
                        raise serializers.ValidationError("The DOCX file is missing its document content.")
            except (zipfile.BadZipFile, OSError):
                raise serializers.ValidationError("The DOCX file is damaged or invalid.")
            finally:
                uploaded_file.seek(0)
        return uploaded_file

    def validate_senior_citizen(self, senior):
        request = self.context.get("request")
        if request and request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile or senior.barangay_id != profile.barangay_id:
                raise serializers.ValidationError("You may only upload documents for seniors in your assigned barangay.")
        return senior


class GenerateSeniorAccountsSerializer(serializers.Serializer):
    senior_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        max_length=100,
    )


class DeathRecordSerializer(serializers.ModelSerializer):
    senior_name = serializers.SerializerMethodField()
    senior_osca_id = serializers.CharField(source="senior_citizen.osca_id", read_only=True)
    senior_address = serializers.CharField(source="senior_citizen.address", read_only=True)
    barangay_name = serializers.CharField(source="senior_citizen.barangay.name", read_only=True, allow_null=True)
    recorded_by_name = serializers.CharField(source="recorded_by.username", read_only=True, allow_null=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.username", read_only=True, allow_null=True)
    pension_status = serializers.SerializerMethodField()

    class Meta:
        model = DeathRecord
        fields = [
            "id", "senior_citizen", "senior_name", "senior_osca_id", "senior_address", "barangay_name",
            "date_of_death", "notes", "review_status", "review_note", "reviewed_by_name", "reviewed_at",
            "pension_status", "recorded_by_name", "created_at",
        ]
        read_only_fields = ["review_status", "review_note", "reviewed_by_name", "reviewed_at", "recorded_by_name", "created_at"]

    def get_senior_name(self, obj):
        senior = obj.senior_citizen
        return f"{senior.first_name} {senior.last_name}".strip()

    def get_pension_status(self, obj):
        return "Pensioner" if obj.senior_citizen.pension_records.exists() else "No pension record"

    def validate_date_of_death(self, value):
        from django.utils import timezone
        if value > timezone.localdate():
            raise serializers.ValidationError("Date of death cannot be in the future.")
        return value

    def validate_senior_citizen(self, senior):
        request = self.context.get("request")
        if hasattr(senior, "death_record"):
            raise serializers.ValidationError("A death record already exists for this senior.")
        if request and request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile or senior.barangay_id != profile.barangay_id:
                raise serializers.ValidationError("You may only record deaths for seniors in your assigned barangay.")
        return senior


class ResidenceTransferRecordSerializer(serializers.ModelSerializer):
    senior_name = serializers.SerializerMethodField()
    senior_osca_id = serializers.CharField(source="senior_citizen.osca_id", read_only=True)
    from_barangay_name = serializers.CharField(source="from_barangay.name", read_only=True)
    to_barangay_name = serializers.CharField(source="to_barangay.name", read_only=True, allow_null=True)
    recorded_by_name = serializers.CharField(source="recorded_by.username", read_only=True, allow_null=True)

    class Meta:
        model = ResidenceTransferRecord
        fields = [
            "id", "senior_citizen", "senior_name", "senior_osca_id",
            "from_barangay", "from_barangay_name", "to_barangay", "to_barangay_name",
            "destination_municipality", "destination_address", "transfer_date", "reason",
            "recorded_by_name", "created_at",
        ]
        read_only_fields = ["from_barangay", "from_barangay_name", "to_barangay_name", "recorded_by_name", "created_at"]

    def get_senior_name(self, obj):
        senior = obj.senior_citizen
        return f"{senior.first_name} {senior.last_name}".strip()

    def validate_transfer_date(self, value):
        from django.utils import timezone
        if value > timezone.localdate():
            raise serializers.ValidationError("Transfer date cannot be in the future.")
        return value

    def validate(self, attrs):
        from rest_framework import serializers as drf_serializers

        request = self.context.get("request")
        senior = attrs.get("senior_citizen")
        destination = attrs.get("to_barangay")
        destination_municipality = attrs.get("destination_municipality", "").strip()
        destination_address = attrs.get("destination_address", "").strip()

        if not destination and not destination_municipality:
            raise drf_serializers.ValidationError({
                "destination_municipality": "Select a destination barangay or enter the destination municipality."
            })
        if not destination and not destination_address:
            raise drf_serializers.ValidationError({
                "destination_address": "Enter the destination address for a transfer outside the listed barangays."
            })
        if senior and not senior.barangay_id:
            raise drf_serializers.ValidationError({"senior_citizen": "This senior has no current barangay recorded."})
        if destination and senior and destination.pk == senior.barangay_id:
            raise drf_serializers.ValidationError({"to_barangay": "The destination is already the senior's barangay."})
        if senior and hasattr(senior, "death_record") and senior.death_record.review_status == "verified":
            raise drf_serializers.ValidationError({"senior_citizen": "A deceased senior cannot be transferred."})
        if request and request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile or not senior or senior.barangay_id != profile.barangay_id:
                raise drf_serializers.ValidationError({"senior_citizen": "You may only transfer seniors in your assigned barangay."})
        return attrs


class PensionRecordSerializer(serializers.ModelSerializer):
    senior_osca_id = serializers.CharField(source="senior_citizen.osca_id", read_only=True)
    senior_name = serializers.SerializerMethodField()

    class Meta:
        model = PensionRecord
        fields = [
            "id", "senior_citizen", "senior_osca_id", "senior_name", "period",
            "amount", "claimed", "date_claimed", "claimed_by", "representative",
            "remarks", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_senior_name(self, obj):
        senior = obj.senior_citizen
        return f"{senior.first_name} {senior.last_name}"

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Pension amount must be greater than zero.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if not request:
            return attrs
        senior = attrs.get("senior_citizen", getattr(self.instance, "senior_citizen", None))
        if senior and hasattr(senior, "death_record") and senior.death_record.review_status == "verified":
            raise serializers.ValidationError({"senior_citizen": "Pension records cannot be created for a senior with a recorded death."})
        if senior and request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile or senior.barangay_id != profile.barangay_id:
                raise serializers.ValidationError({"senior_citizen": "You may only manage seniors in your assigned barangay."})
        return attrs
class GroceryClaimReportSerializer(serializers.ModelSerializer):
    senior_osca_id = serializers.CharField(source="senior_citizen.osca_id", read_only=True)
    senior_name = serializers.SerializerMethodField()
    barangay = serializers.CharField(source="distribution.barangay", read_only=True)
    period = serializers.CharField(source="distribution.period", read_only=True)
    distribution_date = serializers.DateField(source="distribution.distribution_date", read_only=True)
    distribution_status = serializers.CharField(source="distribution.status", read_only=True)

    class Meta:
        model = GroceryClaim
        fields = [
            "id", "senior_citizen", "senior_osca_id", "senior_name", "barangay",
            "period", "distribution_date", "distribution_status", "claimed",
            "date_claimed", "claimed_by", "representative", "remarks",
        ]

    def get_senior_name(self, obj):
        senior = obj.senior_citizen
        return f"{senior.first_name} {senior.last_name}".strip()
