from rest_framework import serializers
from .models import Barangay, PensionRecord, SeniorCitizen

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
            "age",
            "sex",
            "address",
            "barangay",
            "barangay_name",
            "registration_status",
            "is_active",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        if request and request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile:
                raise serializers.ValidationError("This staff account has no assigned barangay.")
            if "barangay" in attrs and attrs["barangay"].id != profile.barangay_id:
                raise serializers.ValidationError({"barangay": "You cannot move a senior citizen to another barangay."})
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
        if senior and request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile or senior.barangay_id != profile.barangay_id:
                raise serializers.ValidationError({"senior_citizen": "You may only manage seniors in your assigned barangay."})
        return attrs
