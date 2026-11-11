"""OSCA-focused, deterministic intent matching and private record lookup."""
import re
import unicodedata

from .models import Document, PensionRecord


def normalize_message(message):
    message = unicodedata.normalize("NFKD", message.casefold())
    message = "".join(char for char in message if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", message).strip()


# Natural question variants in Cebuano and English map to a small, reviewable
# OSCA FAQ. Matching uses normalized phrases so punctuation and accents do not matter.
INTENT_PHRASES = {
    "pension_status": (
        "pension", "pensyon", "social pension", "stipend", "pension claim",
        "claim status", "pila akong pension", "pila akong makuha", "na claim na ba",
        "wala pa na claim", "pension nako", "pension ko", "claim nako",
    ),
    "document_status": (
        "document", "documents", "papel", "papeles", "requirements", "requirement",
        "kulang sa papeles", "kulang sa dokumento", "kulang pa", "na upload",
        "uploaded", "birth certificate", "valid id", "lce endorsement",
    ),
    "registration_requirements": (
        "register", "registration", "magpa rehistro", "magpa register", "pa rehistro", "pagpa rehistro",
        "become a member", "new member", "enroll", "enrol", "requirements sa osca",
        "requirements para sa senior", "requirements para mag member", "unsa dalhon para magpa rehistro",
        "requirements sa pag register", "requirements pag register", "requirements for registration",
        "requirements for applying", "unsa kinahanglan para magparehistro", "unsa dalhon kung magpa register",
    ),
    "profile": (
        "profile", "my name", "akong ngalan", "unsa akong ngalan", "kinsa ko",
        "who am i", "my osca id", "akong osca id", "unsa akong address", "akong edad",
        "my address", "my age",
    ),
    "booklet_guidance": (
        "booklet", "medicine", "medicines", "tambal", "reseta", "medicine purchase",
        "medicine purchase booklet", "nawala ang booklet", "lost booklet", "replacement booklet",
    ),
    "grocery_guidance": (
        "grocery", "groceries", "grocery schedule", "grocery distribution", "grocery claim",
        "kanus a ang grocery", "when is grocery", "grocery nako",
    ),
    "representative": (
        "representative", "authorized representative", "mo claim para nako", "mag claim para nako",
        "anak mag claim", "apo mag claim", "represent kanako", "kinsa pwede mo claim",
    ),
    "lost_id": (
        "lost id", "nawala akong id", "nawala akong osca id", "nawala ang osca id", "replacement id", "ilisan akong id",
        "bag o nga id", "new osca id",
    ),
    "password_help": (
        "forgot password", "nakalimot password", "nakalimot sa password", "reset password",
        "password reset", "dili ko ka login", "cannot log in", "cannot login", "di ko kasulod",
        "di ko ka login", "di ko maka login", "dili ko maka sulod sa account",
    ),
    "contact_staff": (
        "office hours", "oras sa opisina", "oras sa osca", "contact osca", "contact number",
        "telephone number", "asa ang osca", "where is osca", "talk to staff", "istorya sa staff",
    ),
    "osca_purpose": (
        "what is osca", "unsa ang osca", "unsa trabaho sa osca", "purpose sa osca",
        "unsa buhaton sa osca", "what does osca do",
    ),
    "portal_purpose": (
        "unsa gamit sa portal", "unsa gamit sa app", "purpose sa system", "unsa purpose ani",
        "what can this portal do", "what is this system for", "unsa makita diri",
    ),
}

OSCA_TERMS = {
    "osca", "senior", "seniors", "citizen", "citizens", "barangay", "pension", "pensyon",
    "medicine", "tambal", "booklet", "grocery", "osca id", "senior id", "benefit", "benefits",
    "registration", "register", "papeles", "document", "documents", "claim", "claims",
}


def classify_intent(message):
    text = normalize_message(message)
    padded = f" {text} "
    scores = {}
    for intent, phrases in INTENT_PHRASES.items():
        for phrase in phrases:
            normalized_phrase = normalize_message(phrase)
            if normalized_phrase and f" {normalized_phrase} " in padded:
                scores[intent] = scores.get(intent, 0) + 1 + 0.08 * len(normalized_phrase.split())

    if scores:
        # Longer phrase matches add weight, helping a specific FAQ beat a broad word match.
        return max(scores, key=scores.get)
    if any(f" {normalize_message(term)} " in padded for term in OSCA_TERMS):
        return "osca_general"
    return "out_of_scope"


def answer_for_senior(senior, message):
    """Answer OSCA questions and read personal data only from the linked senior record."""
    intent = classify_intent(message)

    if intent == "pension_status":
        record = PensionRecord.objects.filter(senior_citizen=senior).order_by("-period", "-id").first()
        if not record:
            return intent, "Wala pay pension claim record nga makita sa imong portal. Palihug kumpirmaha sa OSCA kung naa kay aktuwal nga claim o schedule."
        status = "na-claim na" if record.claimed else "wala pa ma-claim"
        amount = f"₱{record.amount:,.2f}"
        claimed_date = f" niadtong {record.date_claimed.strftime('%B %d, %Y')}" if record.date_claimed else ""
        return intent, f"Ang pinakabag-ong pension record nimo para sa {record.period} kay {status}, kantidad {amount}{claimed_date}."

    if intent == "document_status":
        docs = Document.objects.filter(senior_citizen=senior)
        total = docs.count()
        if not total:
            return intent, "Wala pay uploaded document nga nakarekord sa imong portal. Pangutana sa OSCA staff kung unsang requirements ang kinahanglan nimo isumite."
        verified = docs.filter(review_status="verified", is_verified=True).count()
        pending = docs.filter(review_status="pending").count()
        return intent, f"Naa kay {total} uploaded document record(s): {verified} verified ug {pending} pending review. Ang OSCA staff ra ang makakumpirma kung kompleto na ang requirements."

    if intent == "registration_requirements":
        return intent, "Sa current portal checklist, ang registration requirements mao ang OSCA Form No. 1, birth certificate o valid ID, 2x2 photo, full-body photo nga gi-print sa A4, ug LCE endorsement letter. Kumpirmaha sa OSCA Carmen staff kay sila ang mo-final sa checklist."

    if intent == "profile":
        full_name = " ".join(part for part in (senior.first_name, senior.middle_name, senior.last_name, senior.suffix) if part)
        barangay = senior.barangay.name if senior.barangay_id else "wala pa natakda"
        return intent, f"Ang imong rehistradong ngalan kay {full_name}; OSCA ID {senior.osca_id}; barangay {barangay}. Kung naay sayop, pakikontak ang OSCA staff aron ipa-update ang record."

    if intent == "booklet_guidance":
        return intent, "Ang medicine entries isulat sa imong physical OSCA medicine purchase booklet. Kini nga portal dili mopuli sa booklet. Dad-a ang booklet ug OSCA ID sa OSCA kung mangayo og tabang o replacement."

    if intent == "grocery_guidance":
        return intent, "Ang grocery assistance ug schedule ipahibalo sa OSCA o sa staff nga nagdumala sa distribution. Kumpirmaha sa OSCA Carmen office o barangay staff; dili pa kini live nga schedule sa portal."

    if intent == "representative":
        return intent, "Ang OSCA FAQ nag-ingon nga ang anak o apo mahimong mo-represent kung rehistrado isip authorized representative. Pangayoa sa OSCA Carmen ang opisyal nga porma ug kumpirmaha ang mga dokumentong dad-on."

    if intent == "lost_id":
        return intent, "Kung nawala ang OSCA ID, ipahibalo dayon sa OSCA Carmen office ug pangayoa ang ilang kasamtangang replacement requirements. Ayaw pagbase sa daang checklist kung wala pa kini makumpirma sa staff."

    if intent == "password_help":
        return intent, "Kung nakalimot ka sa password o dili ka maka-login, bisitaha ang OSCA Carmen office para ma-verify ang imong identity ug matabangan ka sa account access. Wala pay online password-reset flow sa portal."

    if intent == "contact_staff":
        return intent, "Wala pay verified nga contact number o office hours sa portal. Palihug bisitaha ang OSCA Carmen office aron makumpirma ang kasamtangang oras ug serbisyo."

    if intent == "osca_purpose":
        return intent, "Ang OSCA mao ang lokal nga opisina nga nagtabang sa pagdumala sa senior citizen records ug mga serbisyo sa lungsod. Para sa espesipikong serbisyo o eligibility, kumpirmaha sa OSCA Carmen staff."

    if intent == "portal_purpose":
        return intent, "Ang Arkheion senior portal nagpakita sa imong profile, pension history, ug document status nga na-record sa OSCA. Ang portal makatabang sa pagtan-aw sa records pero dili mopuli sa OSCA staff o sa imong physical medicine booklet."

    if intent == "osca_general":
        return intent, "Makatabang ko sa OSCA registration, pension record, uploaded documents, physical medicine booklet, grocery guidance, account access, ug OSCA services. Unsa ani ang gusto nimong ipangutana?"

    return intent, "OSCA Carmen senior services ra akong matabangan. Pwede ka mangutana bahin sa registration, pension, records, medicine booklet, grocery guidance, o account access."
