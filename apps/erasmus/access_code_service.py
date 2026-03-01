"""
ErasmusAccessCodeService
========================

Two-phase WhatsApp magic-link flow, mirroring the reservation code system.

Phase 1 – generate_code(lead, target)
  Called from the API when the student clicks "Acceder" on the gracias page.
  Creates an ErasmusMagicLink with status=pending_whatsapp and returns
  a pre-filled WhatsApp URL the student opens to send their verification message.

Phase 2 – process_incoming_code(whatsapp_message, eras_code)
  Called by MessageProcessor when an ERAS-XXXXX code is detected in an
  incoming WhatsApp message.
  Validates the code, generates the access_token, and sends the personalised
  welcome + magic-link reply back to the student.
"""
import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

CODE_PREFIX = "ERAS"
CODE_EXPIRY_HOURS = 24
LINK_EXPIRY_HOURS = 48

# The Tuki WhatsApp number students message (without + prefix, digits only)
TUKI_WHATSAPP_NUMBER = getattr(settings, "TUKI_WHATSAPP_NUMBER", "56947884342")

# Main WhatsApp group link (used in welcome message)
WHATSAPP_MAIN_GROUP_URL = "https://chat.whatsapp.com/JguF1qVYRGaIwm2ss7QKp1?mode=gi_t"

# Supported form locales for welcome message (same as frontend selector)
WELCOME_LOCALES = ("es", "en", "pt", "de", "it", "fr")

# Welcome message template per locale. Placeholders: {first_name}, {link_plataforma}, {magic_link_url}, {email}
WELCOME_MESSAGES = {
    "es": (
        "Hola {first_name},\n\n"
        "Soy Tatán (Sebastián), creador de Tuki 🙌\n\n"
        "Bienvenido/a a Tuki Erasmus ✨\n\n"
        "En Tuki estamos construyendo la comunidad de intercambio más grande de Chile, y mi objetivo este semestre es ayudar a que vivas una experiencia increíble en Chile, ojalá la mejor de tu vida 🇨🇱\n\n"
        "Llevo más de un año creando experiencias para estudiantes de Erasmus, y honestamente ha sido de las cosas más entretenidas y significativas que he hecho. Solo el semestre pasado participaron más de 300 personas, y quiero que tú también seas parte de eso 🙌\n\n"
        "Durante el semestre vamos a tener paseos y actividades todas las semanas. Puedes ver todo el calendario actualizado en este link, y te podrás inscribir con la cuenta que acabas de crear:\n"
        "tuki.cl/erasmus\n\n"
        "Para acceder por primera vez a tu cuenta y ver los grupos de WhatsApp y los otros miembros de la comunidad puedes hacer click aquí:\n"
        "{link_plataforma}\n\n"
        "Este es nuestro instagram (recién creado): instagram.com/tukierasmus\n\n"
        "Ese link te va a hacer iniciar sesión directamente; siempre podrás acceder a todo desde tu perfil en tuki.cl/account, ingresando con tu correo {email}\n\n"
        "Este es mi instagram (instagram.com/viajestatan), donde subo datos de viajes, lugares en Santiago, Chile y Sudamérica 🌎\n\n"
        "Y obvio, este es mi número. Escríbeme cuando quieras — ya sea por dudas, para organizar viajes, panoramas o cualquier cosa de tu intercambio. Feliz de ayudarte 🤝\n\n"
        "Con mi equipo estamos 100% comprometidos en hacer que tu experiencia Erasmus sea increíble. De verdad nos importa que lo pases bien y aproveches al máximo este semestre 🙌\n\n"
        "Siempre podrás reservar actividades, viajes y alojamientos directamente en nuestra web:\n"
        "Tuki.cl\n\n"
        "¡Nos vemos pronto! 🚀"
    ),
    "en": (
        "Hi {first_name},\n\n"
        "I'm Tatán (Sebastián), creator of Tuki 🙌\n\n"
        "Welcome to Tuki Erasmus ✨\n\n"
        "At Tuki we're building Chile's largest exchange community, and my goal this semester is to help you have an amazing experience in Chile — hopefully the best of your life 🇨🇱\n\n"
        "I've been creating experiences for Erasmus students for over a year, and honestly it's been one of the most fun and meaningful things I've done. Last semester alone over 300 people took part, and I want you to be part of it too 🙌\n\n"
        "During the semester we'll have trips and activities every week. You can see the full updated calendar and sign up with the account you just created here:\n"
        "tuki.cl/erasmus\n\n"
        "To access your account for the first time and see the WhatsApp groups and other community members, you can click here:\n"
        "{link_plataforma}\n\n"
        "This is our Instagram (just created): instagram.com/tukierasmus\n\n"
        "That link will log you in directly; you can always access everything from your profile at tuki.cl/account, using your email {email}\n\n"
        "This is my Instagram (instagram.com/viajestatan), where I post travel tips, places in Santiago, Chile and South America 🌎\n\n"
        "And of course, this is my number. Text me whenever you want — whether for questions, to plan trips, or anything about your exchange. Happy to help 🤝\n\n"
        "With my team we're 100% committed to making your Erasmus experience amazing. We really care that you have a great time and make the most of this semester 🙌\n\n"
        "You can always book activities, trips and accommodation directly on our website:\n"
        "Tuki.cl\n\n"
        "See you soon! 🚀"
    ),
    "pt": (
        "Olá {first_name},\n\n"
        "Sou Tatán (Sebastián), criador da Tuki 🙌\n\n"
        "Bem-vindo/a à Tuki Erasmus ✨\n\n"
        "Na Tuki estamos a construir a maior comunidade de intercâmbio do Chile, e o meu objetivo este semestre é ajudar-te a viver uma experiência incrível no Chile, espero que a melhor da tua vida 🇨🇱\n\n"
        "Há mais de um ano que crio experiências para estudantes Erasmus, e honestamente tem sido das coisas mais divertidas e significativas que fiz. Só no semestre passado participaram mais de 300 pessoas, e quero que tu também faças parte 🙌\n\n"
        "Durante o semestre vamos ter passeios e atividades todas as semanas. Podes ver o calendário atualizado neste link e inscrever-te com a conta que acabaste de criar:\n"
        "tuki.cl/erasmus\n\n"
        "Para acederes à tua conta pela primeira vez e veres os grupos de WhatsApp e os outros membros da comunidade, podes clicar aqui:\n"
        "{link_plataforma}\n\n"
        "Este é o nosso Instagram (recém-criado): instagram.com/tukierasmus\n\n"
        "Esse link vai fazer-te iniciar sessão diretamente; sempre podes aceder a tudo a partir do teu perfil em tuki.cl/account, com o teu email {email}\n\n"
        "Este é o meu Instagram (instagram.com/viajestatan), onde partilho dicas de viagens, lugares em Santiago, Chile e América do Sul 🌎\n\n"
        "E claro, este é o meu número. Escreve-me quando quiseres — dúvidas, organizar viagens ou o que for do teu intercâmbio. Feliz em ajudar 🤝\n\n"
        "Com a minha equipa estamos 100% empenhados em fazer da tua experiência Erasmus incrível. Importa-nos que te divirtas e aproveites ao máximo este semestre 🙌\n\n"
        "Sempre podes reservar atividades, viagens e alojamento diretamente no nosso site:\n"
        "Tuki.cl\n\n"
        "Até breve! 🚀"
    ),
    "de": (
        "Hallo {first_name},\n\n"
        "ich bin Tatán (Sebastián), Schöpfer von Tuki 🙌\n\n"
        "Willkommen bei Tuki Erasmus ✨\n\n"
        "Bei Tuki bauen wir die größte Austausch-Community Chiles, und mein Ziel dieses Semester ist, dir zu einer unglaublichen Erfahrung in Chile zu verhelfen – hoffentlich die beste deines Lebens 🇨🇱\n\n"
        "Seit über einem Jahr gestalte ich Erlebnisse für Erasmus-Studierende, und ehrlich gesagt war es eines der lustigsten und bedeutendsten Dinge, die ich gemacht habe. Allein im letzten Semester haben über 300 Leute teilgenommen, und ich möchte, dass du auch dabei bist 🙌\n\n"
        "Während des Semesters gibt es jede Woche Ausflüge und Aktivitäten. Den aktuellen Kalender und die Anmeldung mit deinem gerade erstellten Konto findest du hier:\n"
        "tuki.cl/erasmus\n\n"
        "Um dich zum ersten Mal in deinem Konto anzumelden und die WhatsApp-Gruppen und andere Community-Mitglieder zu sehen, kannst du hier klicken:\n"
        "{link_plataforma}\n\n"
        "Das ist unser Instagram (frisch erstellt): instagram.com/tukierasmus\n\n"
        "Dieser Link loggt dich direkt ein; du kannst jederzeit alles über dein Profil unter tuki.cl/account mit deiner E-Mail {email} aufrufen.\n\n"
        "Das ist mein Instagram (instagram.com/viajestatan), wo ich Reisetipps, Orte in Santiago, Chile und Südamerika poste 🌎\n\n"
        "Und das ist meine Nummer. Schreib mir, wann du willst – ob Fragen, Reisen planen oder was auch immer zu deinem Austausch. Hilf dir gern 🤝\n\n"
        "Mit meinem Team sind wir zu 100% dabei, dein Erasmus-Erlebnis großartig zu machen. Es ist uns wichtig, dass du eine gute Zeit hast und das Semester optimal nutzt 🙌\n\n"
        "Aktivitäten, Reisen und Unterkünfte kannst du jederzeit direkt auf unserer Webseite buchen:\n"
        "Tuki.cl\n\n"
        "Bis bald! 🚀"
    ),
    "it": (
        "Ciao {first_name},\n\n"
        "sono Tatán (Sebastián), creatore di Tuki 🙌\n\n"
        "Benvenuto/a a Tuki Erasmus ✨\n\n"
        "In Tuki stiamo costruendo la più grande community di scambio del Cile, e il mio obiettivo questo semestre è aiutarti a vivere un'esperienza incredibile in Cile, spero la migliore della tua vita 🇨🇱\n\n"
        "Da oltre un anno creo esperienze per studenti Erasmus, e onestamente è stata una delle cose più divertenti e significative che ho fatto. Solo lo scorso semestre hanno partecipato più di 300 persone, e voglio che anche tu ne faccia parte 🙌\n\n"
        "Durante il semestre avremo gite e attività ogni settimana. Puoi vedere il calendario aggiornato e iscriverti con l'account che hai appena creato qui:\n"
        "tuki.cl/erasmus\n\n"
        "Per accedere per la prima volta al tuo account e vedere i gruppi WhatsApp e gli altri membri della community, puoi cliccare qui:\n"
        "{link_plataforma}\n\n"
        "Questo è il nostro Instagram (appena creato): instagram.com/tukierasmus\n\n"
        "Questo link ti farà accedere direttamente; potrai sempre accedere a tutto dal tuo profilo su tuki.cl/account, con la tua email {email}\n\n"
        "Questo è il mio Instagram (instagram.com/viajestatan), dove posto consigli di viaggio, luoghi a Santiago, Cile e Sudamerica 🌎\n\n"
        "E ovviamente questo è il mio numero. Scrivimi quando vuoi — dubbi, organizzare viaggi o qualsiasi cosa del tuo scambio. Felice di aiutarti 🤝\n\n"
        "Con il mio team siamo impegnati al 100% a rendere la tua esperienza Erasmus incredibile. Ci sta davvero a cuore che tu passi bene e sfrutti al massimo questo semestre 🙌\n\n"
        "Potrai sempre prenotare attività, viaggi e alloggi direttamente sul nostro sito:\n"
        "Tuki.cl\n\n"
        "A presto! 🚀"
    ),
    "fr": (
        "Salut {first_name},\n\n"
        "je suis Tatán (Sebastián), créateur de Tuki 🙌\n\n"
        "Bienvenue sur Tuki Erasmus ✨\n\n"
        "Chez Tuki nous construisons la plus grande communauté d'échange du Chili, et mon objectif ce semestre est de t'aider à vivre une expérience incroyable au Chili, j'espère la meilleure de ta vie 🇨🇱\n\n"
        "Cela fait plus d'un an que je crée des expériences pour les étudiants Erasmus, et honnêtement c'est l'une des choses les plus fun et significatives que j'ai faites. Rien que le semestre dernier plus de 300 personnes ont participé, et je veux que tu en fasses partie 🙌\n\n"
        "Pendant le semestre il y aura des sorties et des activités chaque semaine. Tu peux voir tout le calendrier à jour et t'inscrire avec le compte que tu viens de créer ici :\n"
        "tuki.cl/erasmus\n\n"
        "Pour accéder à ton compte pour la première fois et voir les groupes WhatsApp et les autres membres de la communauté, tu peux cliquer ici :\n"
        "{link_plataforma}\n\n"
        "Voici notre Instagram (tout juste créé) : instagram.com/tukierasmus\n\n"
        "Ce lien te connectera directement ; tu pourras toujours tout accéder depuis ton profil sur tuki.cl/account, avec ton email {email}\n\n"
        "Voici mon Instagram (instagram.com/viajestatan), où je poste des infos voyage, des lieux à Santiago, au Chili et en Amérique du Sud 🌎\n\n"
        "Et bien sûr voici mon numéro. Écris-moi quand tu veux — questions, organiser des voyages ou quoi que ce soit de ton échange. Ravi de t'aider 🤝\n\n"
        "Avec mon équipe nous sommes 100% engagés à faire de ton expérience Erasmus quelque chose d'incroyable. On tient vraiment à ce que tu passes un bon moment et que tu profites au max de ce semestre 🙌\n\n"
        "Tu pourras toujours réserver activités, voyages et hébergements directement sur notre site :\n"
        "Tuki.cl\n\n"
        "À bientôt ! 🚀"
    ),
}


def _generate_verification_code() -> str:
    """Generate a unique ERAS-XXXXXXXX code."""
    from apps.erasmus.models import ErasmusMagicLink

    for _ in range(15):
        rand = secrets.token_hex(3).upper()  # 6 hex chars
        code = f"{CODE_PREFIX}-{rand}"
        if not ErasmusMagicLink.objects.filter(verification_code=code).exists():
            return code
    raise RuntimeError("Could not generate a unique ERAS verification code after 15 attempts.")


def generate_access_code(lead, target: str) -> dict:
    """
    Phase 1: generate a verification code and build the WhatsApp pre-fill URL.

    Returns a dict with:
      - verification_code   e.g. "ERAS-A1B2C3"
      - whatsapp_url        wa.me URL the frontend opens
      - expires_at          ISO string
    """
    from apps.erasmus.models import ErasmusMagicLink

    if target not in (ErasmusMagicLink.TARGET_COMMUNITY, ErasmusMagicLink.TARGET_WHATSAPP):
        raise ValueError(f"Invalid target '{target}'. Must be 'community' or 'whatsapp'.")

    code = _generate_verification_code()
    now = timezone.now()
    expires_at = now + timedelta(hours=CODE_EXPIRY_HOURS)

    magic_link = ErasmusMagicLink.objects.create(
        lead=lead,
        verification_code=code,
        access_token=None,
        target=target,
        status=ErasmusMagicLink.STATUS_PENDING,
        expires_at=expires_at,
    )

    target_label = (
        "la Comunidad Erasmus"
        if target == ErasmusMagicLink.TARGET_COMMUNITY
        else "los Grupos de WhatsApp"
    )
    name = (lead.first_name or "").strip() or "Erasmus"
    pre_fill = (
        f"Hola! Ya completé mi formulario Erasmus Tuki. "
        f"Quiero acceder a {target_label}. "
        f"Mi código: {code}"
    )

    import urllib.parse
    whatsapp_url = f"https://wa.me/{TUKI_WHATSAPP_NUMBER}?text={urllib.parse.quote(pre_fill)}"

    logger.info(
        "[ErasmusAccess] Generated code %s for lead %s target=%s",
        code, lead.id, target,
    )
    return {
        "magic_link_id": str(magic_link.id),
        "verification_code": code,
        "whatsapp_url": whatsapp_url,
        "expires_at": expires_at.isoformat(),
    }


def process_incoming_code(whatsapp_message, eras_code: str) -> bool:
    """
    Phase 2: called when the WhatsApp bot receives an ERAS-XXXXX code.

    Validates the code, generates the access_token, saves the magic link, and
    sends the student a personalised welcome message with their magic link.

    Returns True on success, False if code is invalid/expired.
    """
    from apps.erasmus.models import ErasmusMagicLink
    from apps.whatsapp.services.whatsapp_client import WhatsAppWebService

    try:
        magic = ErasmusMagicLink.objects.select_related("lead").get(
            verification_code=eras_code,
        )
    except ErasmusMagicLink.DoesNotExist:
        logger.warning("[ErasmusAccess] Code %s not found in DB", eras_code)
        return False

    if not magic.is_code_valid:
        logger.warning(
            "[ErasmusAccess] Code %s is not valid (status=%s, expires_at=%s)",
            eras_code, magic.status, magic.expires_at,
        )
        _send_expired_code_message(whatsapp_message, magic.lead)
        return False

    # Generate secure access_token
    now = timezone.now()
    token = secrets.token_urlsafe(32)
    link_expires_at = now + timedelta(hours=LINK_EXPIRY_HOURS)

    magic.access_token = token
    magic.status = ErasmusMagicLink.STATUS_LINK_SENT
    magic.link_expires_at = link_expires_at
    magic.save(update_fields=["access_token", "status", "link_expires_at", "updated_at"])

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:8080").rstrip("/")
    magic_link_url = f"{frontend_url}/erasmus/acceder?token={token}"

    _send_welcome_message(whatsapp_message, magic, magic_link_url)
    logger.info(
        "[ErasmusAccess] Link sent to lead %s (target=%s)", magic.lead.id, magic.target,
    )
    return True


def get_or_create_manual_welcome_link(lead):
    """
    For superadmin "copy welcome message": return a magic link for this lead
    that has a valid access_token (so the URL works when they send the message).
    Reuses an existing valid link if any; otherwise creates a new one with token set.
    Returns (ErasmusMagicLink, magic_link_url: str).
    """
    from apps.erasmus.models import ErasmusMagicLink

    now = timezone.now()
    existing = (
        ErasmusMagicLink.objects.filter(
            lead=lead,
            access_token__isnull=False,
        )
        .exclude(access_token="")
        .filter(link_expires_at__gt=now)
        .order_by("-link_expires_at")
        .first()
    )
    if existing:
        frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
        url = f"{frontend_url}/erasmus/acceder?token={existing.access_token}" if frontend_url else ""
        return existing, url

    code = _generate_verification_code()
    token = secrets.token_urlsafe(32)
    link_expires_at = now + timedelta(hours=LINK_EXPIRY_HOURS)
    expires_at = now + timedelta(hours=CODE_EXPIRY_HOURS)
    magic = ErasmusMagicLink.objects.create(
        lead=lead,
        verification_code=code,
        access_token=token,
        target=ErasmusMagicLink.TARGET_COMMUNITY,
        status=ErasmusMagicLink.STATUS_LINK_SENT,
        expires_at=expires_at,
        link_expires_at=link_expires_at,
    )
    frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    url = f"{frontend_url}/erasmus/acceder?token={token}" if frontend_url else ""
    return magic, url


def get_welcome_message_text(lead, magic_link_url: str) -> str:
    """
    Build the personalised welcome message text for a lead (no send).
    Used for manual sending and by _send_welcome_message.
    """
    locale = (getattr(lead, "form_locale", None) or "").strip().lower() or "es"
    if locale not in WELCOME_LOCALES:
        locale = "es"
    email = (lead.email or "").strip()
    if not email:
        email = {"es": "tu correo", "en": "your email", "pt": "o teu email", "de": "deine E-Mail", "it": "la tua email", "fr": "ton email"}.get(locale, "tu correo")
    first_name = (lead.first_name or "").strip() or {"es": "Erasmus", "en": "there", "pt": "Erasmus", "de": "Erasmus", "it": "Erasmus", "fr": "Erasmus"}.get(locale, "Erasmus")
    template = WELCOME_MESSAGES.get(locale) or WELCOME_MESSAGES["es"]
    return template.format(
        first_name=first_name,
        link_grupos=magic_link_url,
        link_plataforma=magic_link_url,
        magic_link_url=magic_link_url,
        email=email,
    )


def _send_welcome_message(whatsapp_message, magic, magic_link_url: str) -> None:
    """Send the personalised WhatsApp welcome reply in the lead's form language."""
    from apps.whatsapp.services.whatsapp_client import WhatsAppWebService

    lead = magic.lead
    phone = getattr(whatsapp_message, "phone", "") or ""
    message = get_welcome_message_text(lead, magic_link_url)

    try:
        service = WhatsAppWebService()
        clean_phone = service.clean_phone_number(phone) if phone else None
        if clean_phone:
            service.send_message(clean_phone, message)
            logger.info("[ErasmusAccess] Welcome message sent to %s", clean_phone)
        else:
            logger.warning("[ErasmusAccess] No valid phone for welcome message (lead %s)", lead.id)
    except Exception as exc:
        logger.exception("[ErasmusAccess] Failed to send welcome WhatsApp to lead %s: %s", lead.id, exc)


def _send_expired_code_message(whatsapp_message, lead) -> None:
    """Notify the student that their code expired and they need to generate a new one."""
    from apps.whatsapp.services.whatsapp_client import WhatsAppWebService

    phone = getattr(whatsapp_message, "phone", "") or ""
    name = (lead.first_name or "").strip() or "Erasmus"
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:8080").rstrip("/")
    message = (
        f"¡Hola {name}! Tu código de acceso ya no es válido (expiró o ya fue usado).\n\n"
        f"Genera uno nuevo desde la página de confirmación de tu formulario Erasmus:\n"
        f"{frontend_url}/erasmus/registro/gracias\n\n"
        f"¡Estamos aquí para ayudarte! 😊"
    )
    try:
        service = WhatsAppWebService()
        clean_phone = service.clean_phone_number(phone) if phone else None
        if clean_phone:
            service.send_message(clean_phone, message)
    except Exception as exc:
        logger.warning("[ErasmusAccess] Could not send expired-code message to lead %s: %s", lead.id, exc)
