"""
Static options for Erasmus registration form (destinations, interests, countries).
Exposed via GET /api/v1/erasmus/options/; can be replaced by DB later.
"""

# Common countries for "país" (country of origin) – can be extended or loaded from core.Country
COUNTRIES = [
    {"code": "ES", "label": "España"},
    {"code": "FR", "label": "Francia"},
    {"code": "DE", "label": "Alemania"},
    {"code": "IT", "label": "Italia"},
    {"code": "PT", "label": "Portugal"},
    {"code": "NL", "label": "Países Bajos"},
    {"code": "BE", "label": "Bélgica"},
    {"code": "AT", "label": "Austria"},
    {"code": "PL", "label": "Polonia"},
    {"code": "SE", "label": "Suecia"},
    {"code": "GB", "label": "Reino Unido"},
    {"code": "IE", "label": "Irlanda"},
    {"code": "MX", "label": "México"},
    {"code": "AR", "label": "Argentina"},
    {"code": "CO", "label": "Colombia"},
    {"code": "BR", "label": "Brasil"},
    {"code": "US", "label": "Estados Unidos"},
    {"code": "CA", "label": "Canadá"},
    {"code": "AU", "label": "Australia"},
    {"code": "OTHER", "label": "Otro"},
]

DESTINATIONS_BY_COUNTRY = {
    "chile": [
        {"slug": "san-pedro-atacama", "label": "San Pedro de Atacama"},
        {"slug": "carretera-austral", "label": "Carretera Austral"},
        {"slug": "torres-del-paine", "label": "Torres del Paine"},
        {"slug": "pucon", "label": "Pucón"},
        {"slug": "pichilemu", "label": "Pichilemu"},
    ],
    "bolivia": [
        {"slug": "la-paz", "label": "La Paz"},
        {"slug": "salar-uyuni", "label": "Salar de Uyuni"},
        {"slug": "amazonas-pampa-selva", "label": "Amazonas (Pampa y Selva)"},
        {"slug": "carretera-muerte", "label": "Carretera de la Muerte"},
        {"slug": "valle-animas", "label": "Valle de las Ánimas"},
    ],
    "brasil": [
        {"slug": "rio-de-janeiro", "label": "Río de Janeiro"},
        {"slug": "ilha-grande", "label": "Ilha Grande"},
        {"slug": "paraty", "label": "Paraty"},
        {"slug": "buzios", "label": "Búzios"},
        {"slug": "cabo-frio", "label": "Cabo Frio"},
    ],
    "colombia": [
        {"slug": "eje-cafetero", "label": "Eje Cafetero"},
        {"slug": "santa-marta", "label": "Santa Marta"},
        {"slug": "cartagena", "label": "Cartagena de Indias"},
        {"slug": "parque-tayrona", "label": "Parque Nacional Tayrona"},
        {"slug": "islas-rosario", "label": "Islas del Rosario"},
    ],
}

INTERESTS_BY_CATEGORY = [
    {
        "category": "Viajes y Exploración",
        "icon": "✈️",
        "items": [
            {"id": "viajes-aventura", "label": "Viajes de aventura"},
            {"id": "mochilero", "label": "Mochilero"},
            {"id": "destinos-fuera-ruta", "label": "Destinos fuera de los caminos trillados"},
            {"id": "voluntariado", "label": "Voluntariado en el extranjero"},
            {"id": "aprendizaje-idiomas", "label": "Aprendizaje de idiomas"},
            {"id": "fotografia-viajes", "label": "Fotografía de viajes"},
            {"id": "road-trip", "label": "Viajes por carretera"},
            {"id": "inmersión-cultural", "label": "Inmersión cultural"},
            {"id": "tours-ciudad", "label": "Tours por la ciudad"},
            {"id": "ecoturismo", "label": "Ecoturismo"},
        ],
    },
    {
        "category": "Aire libre y Aventura",
        "icon": "⛰️",
        "items": [
            {"id": "senderismo", "label": "Senderismo"},
            {"id": "acampada", "label": "Acampada"},
            {"id": "fotografia-vida-silvestre", "label": "Fotografía de vida silvestre"},
            {"id": "kayak", "label": "Kayak y piragüismo"},
            {"id": "montanismo", "label": "Montañismo"},
            {"id": "buceo", "label": "Buceo"},
            {"id": "observacion-estrellas", "label": "Observación de estrellas"},
            {"id": "surf", "label": "Surf y deportes acuáticos"},
            {"id": "esqui", "label": "Esquí y snowboard"},
        ],
    },
    {
        "category": "Arte y Cultura",
        "icon": "🎨",
        "items": [
            {"id": "fotografia", "label": "Fotografía"},
            {"id": "baile", "label": "Baile"},
            {"id": "diseño-grafico", "label": "Diseño gráfico"},
            {"id": "pintura", "label": "Pintura"},
            {"id": "cine", "label": "Cine y cinematografía"},
            {"id": "teatro", "label": "Teatro y actuación"},
            {"id": "hacer-turismo", "label": "Hacer turismo"},
            {"id": "explorar-cultura", "label": "Explorar la cultura"},
            {"id": "comida-local", "label": "Comer comida local"},
            {"id": "naturaleza", "label": "Pasar tiempo en la naturaleza"},
        ],
    },
    {
        "category": "Música",
        "icon": "🎵",
        "items": [
            {"id": "instrumentos", "label": "Tocar instrumentos"},
            {"id": "festivales-musica", "label": "Festivales de música"},
            {"id": "musica-electronica", "label": "Música electrónica"},
            {"id": "conciertos-vivo", "label": "Escuchar música en vivo"},
        ],
    },
    {
        "category": "Deportes y Fitness",
        "icon": "🎾",
        "items": [
            {"id": "yoga", "label": "Yoga"},
            {"id": "running", "label": "Correr y trotar"},
            {"id": "crossfit", "label": "CrossFit"},
            {"id": "natacion", "label": "Natación"},
            {"id": "ciclismo", "label": "Ciclismo"},
        ],
    },
]


def get_erasmus_options():
    """Return destinations, interests, and countries for the registration form."""
    return {
        "countries": COUNTRIES,
        "destinations": DESTINATIONS_BY_COUNTRY,
        "interests": INTERESTS_BY_CATEGORY,
    }
