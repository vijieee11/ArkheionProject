from rest_framework import serializers
from .models import Barangay, MedicineBooklet, MedicineBookletEntry, PensionRecord, SeniorCitizen

class BarangaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Barangay
        fields = ["id", "code", "name", "municipality"]


class SeniorCitizenSerializer(serializers.ModelSerializer):
    barangay_name = serializers.CharField(
        source="barangay.name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = SeniorCitizen
        fields = [
            "id",
            "osca_id",
            "registration_cert_no",
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "date_of_registration",
            "age",
            "sex",
            "civil_status",
            "address",
            "barangay",
            "barangay_name",
            "has_portal_account",
            "milestone_age",
            "registration_status",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["date_of_registration", "created_at"]

    has_portal_account = serializers.SerializerMethodField()

    def get_has_portal_account(self, obj):
        return obj.portal_users.exists()

    def validate(self, attrs):
        request = self.context.get("request")
        if request and request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile:
                raise serializers.ValidationError("This staff account has no assigned barangay.")
            if "barangay" in attrs and attrs["barangay"].id != profile.barangay_id:
                raise serializers.ValidationError({"barangay": "You cannot move a senior citizen to another barangay."})
        return attrs


class GenerateSeniorAccountsSerializer(serializers.Serializer):
    senior_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        max_length=100,
    )


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
        if senior and request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile or senior.barangay_id != profile.barangay_id:
                raise serializers.ValidationError({"senior_citizen": "You may only manage seniors in your assigned barangay."})
        return attrs


class MedicineBookletEntrySerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.username", read_only=True, allow_null=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.username", read_only=True, allow_null=True)

    class Meta:
        model = MedicineBookletEntry
        fields = [
            "id", "category", "purchase_date", "description", "quantity", "proof_image",
            "review_status", "uploaded_by_name", "uploaded_at", "reviewed_by_name",
            "reviewed_at", "review_note",
        ]
        read_only_fields = [
            "review_status", "uploaded_by_name", "uploaded_at", "reviewed_by_name",
            "reviewed_at", "review_note",
        ]

    def validate_proof_image(self, value):
        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("Upload a JPG, PNG, or WEBP image.")
        if value.size > 8 * 1024 * 1024:
            raise serializers.ValidationError("Image must be 8 MB or smaller.")
        return value


class MedicineBookletSerializer(serializers.ModelSerializer):
    senior_name = serializers.SerializerMethodField()
    senior_osca_id = serializers.CharField(source="senior_citizen.osca_id", read_only=True)
    barangay_name = serializers.CharField(source="senior_citizen.barangay.name", read_only=True, allow_null=True)
    backup_entries = MedicineBookletEntrySerializer(many=True, read_only=True)

    class Meta:
        model = MedicineBooklet
        fields = [
            "id", "senior_citizen", "senior_name", "senior_osca_id", "barangay_name",
            "booklet_number", "date_issued", "place_issued", "is_active", "status",
            "full_at", "loss_status", "loss_reported_at", "loss_note", "loss_reviewed_at",
            "digital_replacement_issued_at", "backup_entries", "created_at",
        ]
        read_only_fields = [
            "senior_name", "senior_osca_id", "barangay_name", "is_active", "status", "full_at",
            "loss_status", "loss_reported_at", "loss_note", "loss_reviewed_at",
            "digital_replacement_issued_at", "backup_entries", "created_at",
        ]

    def get_senior_name(self, obj):
        senior = obj.senior_citizen
        return f"{senior.first_name} {senior.last_name}".strip()


class MedicineBookletIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicineBooklet
        fields = ["senior_citizen", "booklet_number", "date_issued", "place_issued"]

    def validate_senior_citizen(self, senior):
        request = self.context.get("request")
        if request and request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile or senior.barangay_id != profile.barangay_id:
                raise serializers.ValidationError("You may only issue a booklet to a senior in your assigned barangay.")
        if MedicineBooklet.objects.filter(senior_citizen=senior).exists():
            raise serializers.ValidationError("A physical booklet has already been issued to this senior. Use the digital backup instead.")
        return senior


class MedicineBookletEntryCreateSerializer(MedicineBookletEntrySerializer):
    booklet = serializers.PrimaryKeyRelatedField(queryset=MedicineBooklet.objects.all(), write_only=True)

    class Meta(MedicineBookletEntrySerializer.Meta):
        fields = MedicineBookletEntrySerializer.Meta.fields + ["booklet"]

    def validate_booklet(self, booklet):
        request = self.context.get("request")
        if not request or request.user.role != "senior":
            raise serializers.ValidationError("Only the senior citizen account can upload booklet backup entries.")
        if not request.user.senior_citizen_id or booklet.senior_citizen_id != request.user.senior_citizen_id:
            raise serializers.ValidationError("You may only upload to your own booklet.")
        if booklet.status != "issued" or not booklet.is_active:
            raise serializers.ValidationError("This booklet is no longer accepting entries.")
        return booklet
