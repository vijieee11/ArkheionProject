from io import BytesIO
from pathlib import Path
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import (
    AuditLog, Barangay, BarangayPopulationSnapshot, BookletReturn, Document, GroceryClaim,
    DeathRecord, GroceryDistribution, PensionRecord, SeniorCitizen, StaffProfile,
)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DocumentWorkflowTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.media_dir.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

        User = get_user_model()
        self.head = User.objects.create_user("head", password="TestPassword.2026", role="head_staff")
        self.staff = User.objects.create_user("staff", password="TestPassword.2026", role="regular_staff")
        self.other_staff = User.objects.create_user("other", password="TestPassword.2026", role="regular_staff")
        self.senior_user = User.objects.create_user("senior", password="TestPassword.2026", role="senior")
        self.carmen = Barangay.objects.create(name="Carmen", code="CARMEN")
        self.other_barangay = Barangay.objects.create(name="Alejal", code="ALEJAL")
        StaffProfile.objects.create(user=self.staff, barangay=self.carmen)
        StaffProfile.objects.create(user=self.other_staff, barangay=self.other_barangay)
        self.senior = self.make_senior("SC-001", self.carmen)
        self.other_senior = self.make_senior("SC-002", self.other_barangay)
        self.client = APIClient()

    def make_senior(self, osca_id, barangay):
        return SeniorCitizen.objects.create(
            osca_id=osca_id,
            registration_cert_no=f"CERT-{osca_id}",
            first_name="Maria",
            last_name="Sample",
            date_of_birth="1940-01-01",
            age=86,
            sex="F",
            place_of_birth="Carmen",
            civil_status="widowed",
            address="Sample address",
            barangay=barangay,
        )

    @staticmethod
    def png_file(name="sample.png"):
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (20, 20), color="white").save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def make_document(self, senior=None):
        return Document.objects.create(
            senior_citizen=senior or self.senior,
            document_type="Birth certificate",
            file=SimpleUploadedFile("sample.png", b"\x89PNG\r\n\x1a\n" + b"test", content_type="image/png"),
            file_name="sample.png",
            uploaded_by=self.staff,
        )

    def test_upload_runs_ocr_and_classifier_and_starts_pending_review(self):
        from unittest.mock import patch

        self.client.force_authenticate(self.staff)
        with patch("core.views.extract_document_text", return_value=("sample text", "ocr_complete")), patch(
            "core.views.classify_document", return_value=("Birth certificate", 0.91)
        ):
            response = self.client.post(
                "/api/documents/",
                {
                    "senior_citizen": self.senior.pk,
                    "document_type": "Other",
                    "file": self.png_file(),
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["ocr_status"], "ocr_complete")
        self.assertEqual(response.data["nlp_classification"], "Birth certificate")
        self.assertEqual(response.data["classifier_source"], "")
        self.assertEqual(response.data["review_status"], "pending")
        self.assertFalse(response.data["is_verified"])

    def test_ocr_extracts_only_explicit_fields_as_unverified_response_draft(self):
        from unittest.mock import patch

        self.client.force_authenticate(self.staff)
        ocr_text = "OSCA ID No.: 2026-001\nLAST NAME: SAMPLE\nFIRST NAME: MARIA\nDATE OF BIRTH: 04/18/1941"
        with patch("core.views.extract_document_text", return_value=(ocr_text, "ocr_complete")), patch(
            "core.views.classify_document", return_value=None
        ):
            response = self.client.post(
                "/api/documents/",
                {"senior_citizen": self.senior.pk, "document_type": "Government ID", "file": self.png_file()},
                format="multipart",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["extracted_entities_draft"].get("osca_id"), "2026-001")
        self.assertEqual(response.data["extracted_entities_draft"].get("first_name"), "MARIA")
        self.assertEqual(response.data["extracted_entities_draft"].get("date_of_birth"), "04/18/1941")
        stored = Document.objects.get(pk=response.data["id"])
        self.assertIsNone(stored.extracted_entities)

    def test_upload_rejects_a_file_whose_extension_does_not_match_contents(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            "/api/documents/",
            {
                "senior_citizen": self.senior.pk,
                "document_type": "Birth certificate",
                "file": SimpleUploadedFile("not-a-pdf.pdf", b"plain text", content_type="application/pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.data)

    def test_staff_can_correct_type_and_verify_and_review_is_audited(self):
        document = self.make_document()
        self.client.force_authenticate(self.staff)
        response = self.client.patch(
            f"/api/documents/{document.pk}/review/",
            {"decision": "verify", "document_type": "OSCA Form No. 1", "review_note": "Checked against original."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        document.refresh_from_db()
        self.assertTrue(document.is_verified)
        self.assertEqual(document.review_status, "verified")
        self.assertEqual(document.document_type, "OSCA Form No. 1")
        self.assertEqual(document.reviewed_by, self.staff)
        self.assertTrue(document.reviewed_at)
        self.assertEqual(document.review_note, "Checked against original.")

    def test_staff_can_reject_without_marking_as_verified(self):
        document = self.make_document()
        self.client.force_authenticate(self.staff)
        response = self.client.patch(
            f"/api/documents/{document.pk}/review/",
            {"decision": "reject", "review_note": "Wrong type."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        document.refresh_from_db()
        self.assertEqual(document.review_status, "rejected")
        self.assertFalse(document.is_verified)

    def test_staff_is_limited_to_documents_in_assigned_barangay(self):
        document = self.make_document(self.other_senior)
        self.client.force_authenticate(self.staff)
        response = self.client.patch(
            f"/api/documents/{document.pk}/review/", {"decision": "verify"}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_list_and_download_are_scoped_to_staff_barangay(self):
        local_document = self.make_document(self.senior)
        self.make_document(self.other_senior)
        self.client.force_authenticate(self.staff)
        listing = self.client.get("/api/documents/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([row["id"] for row in listing.data], [local_document.pk])
        denied = self.client.get(f"/api/documents/{Document.objects.exclude(pk=local_document.pk).get().pk}/download/")
        self.assertEqual(denied.status_code, 404)

    def test_delete_removes_file_and_database_record(self):
        document = self.make_document()
        file_name = document.file.name
        self.assertTrue(document.file.storage.exists(file_name))
        self.client.force_authenticate(self.staff)
        response = self.client.delete(f"/api/documents/{document.pk}/review/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Document.objects.filter(pk=document.pk).exists())
        self.assertFalse(document.file.storage.exists(file_name))

    def test_head_staff_can_review_any_barangay_but_seniors_cannot(self):
        document = self.make_document(self.other_senior)
        self.client.force_authenticate(self.senior_user)
        denied = self.client.patch(
            f"/api/documents/{document.pk}/review/", {"decision": "verify"}, format="json"
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.head)
        allowed = self.client.patch(
            f"/api/documents/{document.pk}/review/", {"decision": "verify"}, format="json"
        )
        self.assertEqual(allowed.status_code, 200)

    def test_staff_senior_list_and_detail_stay_within_assigned_barangay(self):
        self.client.force_authenticate(self.staff)
        listing = self.client.get("/api/seniors/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([row["id"] for row in listing.data], [self.senior.pk])
        self.assertEqual(self.client.get(f"/api/seniors/{self.other_senior.pk}/").status_code, 404)

        self.client.force_authenticate(self.head)
        all_records = self.client.get("/api/seniors/")
        self.assertEqual(all_records.status_code, 200)
        self.assertEqual({row["id"] for row in all_records.data}, {self.senior.pk, self.other_senior.pk})

    def test_senior_can_only_view_own_profile_and_pension_records(self):
        self.senior_user.senior_citizen = self.senior
        self.senior_user.save(update_fields=["senior_citizen"])
        own_pension = PensionRecord.objects.create(senior_citizen=self.senior, period="2026-10")
        other_pension = PensionRecord.objects.create(senior_citizen=self.other_senior, period="2026-10")

        self.client.force_authenticate(self.senior_user)
        self.assertEqual(self.client.get(f"/api/seniors/{self.senior.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/seniors/{self.other_senior.pk}/").status_code, 404)
        history = self.client.get("/api/pensions/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual([row["id"] for row in history.data], [own_pension.pk])
        filtered_history = self.client.get(f"/api/pensions/?senior={self.other_senior.pk}")
        self.assertEqual(filtered_history.status_code, 200)
        self.assertEqual(filtered_history.data, [])

        self.client.force_authenticate(self.head)
        head_history = self.client.get("/api/pensions/")
        self.assertEqual({row["id"] for row in head_history.data}, {own_pension.pk, other_pension.pk})

    def test_senior_document_history_returns_only_own_metadata(self):
        self.senior_user.senior_citizen = self.senior
        self.senior_user.save(update_fields=["senior_citizen"])
        own_document = self.make_document(self.senior)
        other_document = self.make_document(self.other_senior)

        self.client.force_authenticate(self.senior_user)
        response = self.client.get("/api/my/documents/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [own_document.pk])
        self.assertEqual(response.data[0]["file_name"], "sample.png")
        self.assertNotIn("file", response.data[0])
        self.assertNotIn("extracted_entities", response.data[0])

    def test_verified_death_deactivates_linked_accounts_and_preserves_records(self):
        self.senior_user.senior_citizen = self.senior
        self.senior_user.save(update_fields=["senior_citizen"])
        pension = PensionRecord.objects.create(senior_citizen=self.senior, period="2026-10")
        document = self.make_document(self.senior)
        death = DeathRecord.objects.create(
            senior_citizen=self.senior,
            date_of_death="2026-10-20",
            recorded_by=self.staff,
            review_status="pending",
        )

        self.client.force_authenticate(self.head)
        response = self.client.patch(
            f"/api/deaths/{death.pk}/review/", {"decision": "verify"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.senior.refresh_from_db()
        self.senior_user.refresh_from_db()
        self.assertFalse(self.senior.is_active)
        self.assertFalse(self.senior_user.is_active)
        self.assertTrue(SeniorCitizen.objects.filter(pk=self.senior.pk).exists())
        self.assertTrue(PensionRecord.objects.filter(pk=pension.pk).exists())
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())
        self.assertTrue(DeathRecord.objects.filter(pk=death.pk, review_status="verified").exists())

        login = self.client.post(
            "/api/token/", {"username": self.senior_user.username, "password": "TestPassword.2026"},
            format="json",
        )
        self.assertEqual(login.status_code, 401)

    def test_returning_death_report_does_not_deactivate_senior(self):
        self.senior_user.senior_citizen = self.senior
        self.senior_user.save(update_fields=["senior_citizen"])
        death = DeathRecord.objects.create(
            senior_citizen=self.senior,
            date_of_death="2026-10-20",
            recorded_by=self.staff,
            review_status="pending",
        )

        self.client.force_authenticate(self.head)
        response = self.client.patch(
            f"/api/deaths/{death.pk}/review/",
            {"decision": "return", "review_note": "Please confirm the date."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.senior.refresh_from_db()
        self.senior_user.refresh_from_db()
        self.assertTrue(self.senior.is_active)
        self.assertTrue(self.senior_user.is_active)

    def test_staff_cannot_read_or_create_pension_records_for_another_barangay(self):
        other_pension = PensionRecord.objects.create(senior_citizen=self.other_senior, period="2026-10")
        self.client.force_authenticate(self.staff)
        history = self.client.get(f"/api/pensions/?senior={self.other_senior.pk}")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data, [])
        self.assertEqual(self.client.get(f"/api/pensions/{other_pension.pk}/").status_code, 404)
        create = self.client.post(
            "/api/pensions/create/",
            {"senior_citizen": self.other_senior.pk, "period": "2026-11", "amount": "500.00"},
            format="json",
        )
        self.assertEqual(create.status_code, 400)

    def test_staff_settings_are_saved_per_account_and_reject_non_staff(self):
        self.client.force_authenticate(self.staff)
        updated = self.client.patch(
            "/api/staff/settings/",
            {
                "contact_number": "09123456789",
                "notifications": {"registration": False, "system": True},
                "preferences": {"landing_page": "members.html", "per_page": 25},
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["contact_number"], "09123456789")
        self.assertFalse(updated.data["notifications"]["registration"])
        self.assertTrue(updated.data["notifications"]["system"])
        self.assertEqual(updated.data["preferences"]["landing_page"], "members.html")
        self.assertEqual(updated.data["preferences"]["per_page"], 25)

        self.staff.refresh_from_db()
        self.assertEqual(self.staff.contact_number, "09123456789")
        self.assertEqual(self.client.get("/api/staff/settings/").data["preferences"]["per_page"], 25)

        self.client.force_authenticate(self.senior_user)
        self.assertEqual(self.client.get("/api/staff/settings/").status_code, 403)

    def test_population_api_exposes_only_verified_rows_in_staff_barangay(self):
        from django.utils import timezone

        rows = [
            BarangayPopulationSnapshot.objects.create(
                barangay=self.carmen, reference_year=2025, resident_population=12000,
                source="OSCA registry", is_verified=True, verified_by=self.head,
                verified_at=timezone.now(),
            ),
            BarangayPopulationSnapshot.objects.create(
                barangay=self.carmen, reference_year=2023, resident_population=11500,
                source="OSCA archive", is_verified=True, verified_by=self.head,
                verified_at=timezone.now(),
            ),
            BarangayPopulationSnapshot.objects.create(
                barangay=self.other_barangay, reference_year=2025, resident_population=8500,
                source="OSCA registry", is_verified=True, verified_by=self.head,
                verified_at=timezone.now(),
            ),
            BarangayPopulationSnapshot.objects.create(
                barangay=self.carmen, reference_year=2026, resident_population=12500,
                source="Unreviewed estimate", is_verified=False,
            ),
            BarangayPopulationSnapshot.objects.create(
                barangay=self.carmen, reference_year=2024, resident_population=11800,
                source="Incomplete verification", is_verified=True,
            ),
        ]

        self.client.force_authenticate(self.staff)
        response = self.client.get("/api/barangay-population/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["id"] for row in response.data}, {rows[0].pk, rows[1].pk})
        self.assertEqual(self.client.get("/api/barangay-population/?reference_year=2023").data[0]["id"], rows[1].pk)
        self.assertEqual(self.client.get("/api/barangay-population/?reference_year=not-a-year").status_code, 400)
        self.assertEqual(self.client.get("/api/barangay-population/?reference_year=1800").status_code, 400)
        self.assertEqual(self.client.post("/api/barangay-population/", {}, format="json").status_code, 405)

        self.client.force_authenticate(self.other_staff)
        other_response = self.client.get("/api/barangay-population/")
        self.assertEqual([row["id"] for row in other_response.data], [rows[2].pk])

        self.client.force_authenticate(self.head)
        head_response = self.client.get("/api/barangay-population/")
        self.assertEqual({row["id"] for row in head_response.data}, {rows[0].pk, rows[1].pk, rows[2].pk})

        self.client.force_authenticate(self.senior_user)
        self.assertEqual(self.client.get("/api/barangay-population/").status_code, 403)

    def test_population_snapshot_validates_reference_year_and_nonzero_total(self):
        valid = BarangayPopulationSnapshot(
            barangay=self.carmen, reference_year=2025, resident_population=12000,
            source="OSCA registry",
        )
        valid.full_clean()

        for year, total in ((1899, 12000), (2101, 12000), (2025, 0)):
            with self.subTest(year=year, total=total):
                invalid = BarangayPopulationSnapshot(
                    barangay=self.carmen, reference_year=year,
                    resident_population=total, source="OSCA registry",
                )
                with self.assertRaises(DjangoValidationError):
                    invalid.full_clean()



@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StaffReportDataFlowTests(TestCase):
    """Exercise each report page's authenticated data sources with multiple staff scopes."""

    def setUp(self):
        User = get_user_model()
        self.head = User.objects.create_user("report_head", password="TestPassword.2026", role="head_staff")
        self.ising_staff = User.objects.create_user("report_ising", password="TestPassword.2026", role="regular_staff")
        # Carmen is the municipality/main office located in Ising, not a separate
        # barangay assignment. Test Ising plus independent barangays instead.
        self.tuganay_staff = User.objects.create_user("report_tuganay", password="TestPassword.2026", role="regular_staff")
        self.alejal_staff = User.objects.create_user("report_alejal", password="TestPassword.2026", role="regular_staff")

        self.ising = Barangay.objects.create(name="Ising", code="ISING")
        self.tuganay = Barangay.objects.create(name="Tuganay", code="TUGANAY")
        self.alejal = Barangay.objects.create(name="Alejal", code="ALEJAL")
        StaffProfile.objects.create(user=self.ising_staff, barangay=self.ising)
        StaffProfile.objects.create(user=self.tuganay_staff, barangay=self.tuganay)
        StaffProfile.objects.create(user=self.alejal_staff, barangay=self.alejal)

        self.ising_senior = self.make_senior("ISING-001", self.ising, "Ising")
        self.tuganay_senior = self.make_senior("TUGANAY-001", self.tuganay, "Tuganay")
        self.alejal_senior = self.make_senior("ALEJAL-001", self.alejal, "Alejal")

        self.ising_pension = PensionRecord.objects.create(
            senior_citizen=self.ising_senior, period="2026-11", amount="500.00", claimed=True,
            date_claimed="2026-11-05",
        )
        self.tuganay_pension = PensionRecord.objects.create(
            senior_citizen=self.tuganay_senior, period="2026-11", amount="500.00", claimed=False,
        )
        self.alejal_pension = PensionRecord.objects.create(
            senior_citizen=self.alejal_senior, period="2026-11", amount="500.00", claimed=True,
            date_claimed="2026-11-06",
        )

        self.ising_distribution = GroceryDistribution.objects.create(
            distribution_date="2026-11-04", barangay="Ising", period="2026-11",
        )
        self.tuganay_distribution = GroceryDistribution.objects.create(
            distribution_date="2026-11-04", barangay="Tuganay", period="2026-11",
        )
        self.alejal_distribution = GroceryDistribution.objects.create(
            distribution_date="2026-11-04", barangay="Alejal", period="2026-11",
        )
        self.ising_claim = GroceryClaim.objects.create(
            distribution=self.ising_distribution, senior_citizen=self.ising_senior, claimed=True,
            date_claimed="2026-11-04", claimed_by="self",
        )
        self.tuganay_claim = GroceryClaim.objects.create(
            distribution=self.tuganay_distribution, senior_citizen=self.tuganay_senior, claimed=False,
        )
        self.alejal_claim = GroceryClaim.objects.create(
            distribution=self.alejal_distribution, senior_citizen=self.alejal_senior, claimed=True,
            date_claimed="2026-11-04", claimed_by="self",
        )

        self.ising_booklet_return = BookletReturn.objects.create(
            senior_citizen=self.ising_senior, date_returned="2026-11-07", recorded_by=self.ising_staff,
        )
        self.tuganay_booklet_return = BookletReturn.objects.create(
            senior_citizen=self.tuganay_senior, date_returned="2026-11-07", recorded_by=self.tuganay_staff,
        )
        self.client = APIClient()

    @staticmethod
    def make_senior(osca_id, barangay, name):
        return SeniorCitizen.objects.create(
            osca_id=osca_id, registration_cert_no=f"CERT-{osca_id}",
            first_name=name, last_name="ReportTest", date_of_birth="1940-01-01", age=86,
            sex="F", place_of_birth=name, civil_status="widowed", address="Sample address",
            barangay=barangay, registration_status="complete",
        )

    def report_sources(self, user):
        self.client.force_authenticate(user)
        return {
            "seniors": self.client.get("/api/seniors/"),
            "pensions": self.client.get("/api/pensions/"),
            "grocery": self.client.get("/api/grocery/claims/"),
            "dashboard_grocery_summary": self.client.get("/api/grocery/dashboard-summary/"),
        }

    def test_report_sources_return_only_the_authenticated_staff_barangay(self):
        cases = [
            (self.ising_staff, self.ising_senior, self.ising_pension, self.ising_claim),
            (self.tuganay_staff, self.tuganay_senior, self.tuganay_pension, self.tuganay_claim),
            (self.alejal_staff, self.alejal_senior, self.alejal_pension, self.alejal_claim),
        ]
        for staff, senior, pension, claim in cases:
            with self.subTest(barangay=staff.staff_profile.barangay.name):
                responses = self.report_sources(staff)
                self.assertEqual(responses["seniors"].status_code, 200)
                self.assertEqual([row["id"] for row in responses["seniors"].data], [senior.pk])
                self.assertEqual(responses["pensions"].status_code, 200)
                self.assertEqual([row["id"] for row in responses["pensions"].data], [pension.pk])
                if staff is self.ising_staff:
                    self.assertEqual(responses["grocery"].status_code, 200)
                    self.assertEqual(
                        {row["id"] for row in responses["grocery"].data},
                        {self.ising_claim.pk, self.tuganay_claim.pk, self.alejal_claim.pk},
                    )
                else:
                    self.assertEqual(responses["grocery"].status_code, 403)
                # Dashboard aggregate is intentionally visible to every staff account.
                self.assertEqual(responses["dashboard_grocery_summary"].status_code, 200)
                self.assertEqual(responses["dashboard_grocery_summary"].data["total_released"], 2)

    def test_booklet_report_is_available_only_to_ising_and_covers_all_barangays(self):
        for staff in (self.tuganay_staff, self.alejal_staff):
            self.client.force_authenticate(staff)
            response = self.client.get("/api/booklet-returns/")
            self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(self.ising_staff)
        response = self.client.get("/api/booklet-returns/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {row["id"] for row in response.data},
            {self.ising_booklet_return.pk, self.tuganay_booklet_return.pk},
        )
        senior_options = self.client.get("/api/booklet-returns/seniors/")
        self.assertEqual(senior_options.status_code, 200)
        self.assertEqual(
            {row["id"] for row in senior_options.data},
            {self.ising_senior.pk, self.tuganay_senior.pk, self.alejal_senior.pk},
        )

    def test_ising_only_account_can_create_grocery_distribution_and_booklet_return(self):
        distribution_payload = {
            "distribution_date": "2026-11-09", "distribution_time": "09:00",
            "barangay": "Tuganay", "period": "2026-11", "status": "scheduled",
        }
        self.client.force_authenticate(self.tuganay_staff)
        denied_distribution = self.client.post("/api/grocery/distributions/", distribution_payload, format="json")
        denied_grocery_report = self.client.get("/api/grocery/claims/")
        denied_distribution_list = self.client.get("/api/grocery/distributions/")
        denied_return = self.client.post(
            "/api/booklet-returns/",
            {"senior_citizen": self.tuganay_senior.pk, "date_returned": "2026-11-09"},
            format="json",
        )
        self.assertEqual(denied_distribution.status_code, 403)
        self.assertEqual(denied_grocery_report.status_code, 403)
        self.assertEqual(denied_distribution_list.status_code, 403)
        self.assertEqual(denied_return.status_code, 403)

        self.client.force_authenticate(self.ising_staff)
        allowed_grocery_report = self.client.get("/api/grocery/claims/")
        allowed_distribution_list = self.client.get("/api/grocery/distributions/")
        allowed_distribution = self.client.post("/api/grocery/distributions/", distribution_payload, format="json")
        allowed_return = self.client.post(
            "/api/booklet-returns/",
            {"senior_citizen": self.tuganay_senior.pk, "date_returned": "2026-11-09"},
            format="json",
        )
        allowed_foreign_distribution_claim = self.client.post(
            "/api/grocery/claims/",
            {
                "distribution": allowed_distribution.data["id"],
                "senior_citizen": self.tuganay_senior.pk,
                "claimed": True,
                "date_claimed": "2026-11-09",
                "claimed_by": "self",
            },
            format="json",
        )
        self.assertEqual(allowed_grocery_report.status_code, 200)
        self.assertEqual(
            {row["id"] for row in allowed_grocery_report.data},
            {self.ising_claim.pk, self.tuganay_claim.pk, self.alejal_claim.pk},
        )
        self.assertEqual(allowed_distribution_list.status_code, 200)
        self.assertEqual(
            {row["id"] for row in allowed_distribution_list.data},
            {self.ising_distribution.pk, self.tuganay_distribution.pk, self.alejal_distribution.pk},
        )
        self.assertEqual(allowed_distribution.status_code, 201)
        self.assertEqual(allowed_distribution.data["total_beneficiaries"], 1)
        self.assertEqual(allowed_return.status_code, 201)
        self.assertEqual(allowed_foreign_distribution_claim.status_code, 201)

    def test_staff_cannot_export_another_barangays_pension_by_querying_its_senior_id(self):
        self.client.force_authenticate(self.ising_staff)
        response = self.client.get(f"/api/pensions/?senior={self.alejal_senior.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_headstaff_pdf_export_is_server_generated_scoped_and_audited(self):
        self.client.force_authenticate(self.head)
        response = self.client.get(
            "/api/headstaff/reports/masterlist/pdf/?month=2026-11&barangay=Ising"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("masterlist-2026-11-ising.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-"))
        export = AuditLog.objects.get(module="report_export", action="export")
        self.assertIn("scope=Ising", export.description)
        self.assertIn("rows=1", export.description)

    def test_report_pdf_endpoint_rejects_non_headstaff_and_invalid_filters(self):
        self.client.force_authenticate(self.ising_staff)
        forbidden = self.client.get("/api/headstaff/reports/masterlist/pdf/?month=2026-11")
        self.assertEqual(forbidden.status_code, 403)

        self.client.force_authenticate(self.head)
        invalid_month = self.client.get("/api/headstaff/reports/masterlist/pdf/?month=2026-13")
        invalid_barangay = self.client.get("/api/headstaff/reports/masterlist/pdf/?barangay=NotARealBarangay")
        self.assertEqual(invalid_month.status_code, 400)
        self.assertEqual(invalid_barangay.status_code, 400)

    def test_every_headstaff_report_template_generates_a_pdf(self):
        self.client.force_authenticate(self.head)
        for report_key in ("ncsc_annex_a", "pension_payroll", "masterlist", "quarterly_analytics"):
            with self.subTest(report=report_key):
                response = self.client.get(
                    f"/api/headstaff/reports/{report_key}/pdf/?month=2026-11&barangay=All"
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertTrue(response.content.startswith(b"%PDF-"))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SeniorChatbotTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.barangay = Barangay.objects.create(name="Carmen", code="CHAT-CARMEN")
        self.senior = SeniorCitizen.objects.create(
            osca_id="CHAT-001", registration_cert_no="CHAT-CERT-001",
            first_name="Maria", middle_name="Sample", last_name="Senior",
            date_of_birth="1940-01-01", age=86, sex="F", place_of_birth="Carmen",
            civil_status="widowed", address="Sample address", barangay=self.barangay,
        )
        self.other_senior = SeniorCitizen.objects.create(
            osca_id="CHAT-002", registration_cert_no="CHAT-CERT-002",
            first_name="Jose", last_name="Other", date_of_birth="1941-01-01", age=85,
            sex="M", place_of_birth="Carmen", civil_status="married", address="Other address",
            barangay=self.barangay,
        )
        self.user = User.objects.create_user("chat_senior", password="TestPassword.2026", role="senior", senior_citizen=self.senior)
        self.staff = User.objects.create_user("chat_staff", password="TestPassword.2026", role="regular_staff")
        self.client = APIClient()

    def test_osca_intent_detection_handles_question_variations_and_scope(self):
        from .chatbot import classify_intent

        cases = {
            "Pila man akong makuha sa pensyon?": "pension_status",
            "Unsa akong kulang sa papeles?": "document_status",
            "Unsa ang requirements sa pag register?": "registration_requirements",
            "Nawala akong OSCA ID, unsay buhaton?": "lost_id",
            "Di ko maka login sa account": "password_help",
            "Unsa ang purpose sa system?": "portal_purpose",
            "Unsa imong paboritong pagkaon?": "out_of_scope",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(classify_intent(message), expected)

    def test_chatbot_answers_with_only_authenticated_senior_pension_data(self):
        PensionRecord.objects.create(
            senior_citizen=self.senior, period="2026-10", amount="500.00",
            claimed=True, date_claimed="2026-10-05",
        )
        PensionRecord.objects.create(
            senior_citizen=self.other_senior, period="2026-11", amount="700.00", claimed=False,
        )
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/chatbot/", {"message": "Unsa akong pension status?"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["intent"], "pension_status")
        self.assertIn("2026-10", response.data["answer"])
        self.assertIn("₱500.00", response.data["answer"])
        self.assertNotIn("2026-11", response.data["answer"])

    def test_chatbot_rejects_staff_and_invalid_questions(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post("/api/chatbot/", {"message": "hello"}, format="json").status_code, 403)

        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post("/api/chatbot/", {"message": " "}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/chatbot/", {"message": "x" * 501}, format="json").status_code, 400)

