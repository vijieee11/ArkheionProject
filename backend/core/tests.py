from io import BytesIO
from pathlib import Path
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Barangay, Document, PensionRecord, SeniorCitizen, StaffProfile


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

