"""Default message templates for operators - formal tone, no emojis."""

DEFAULT_TEMPLATES = {
    'reservation_request': """Nueva solicitud de reserva

Hola {{contacto}},

Experiencia: {{experiencia}}
Fecha: {{fecha}}
Hora: {{hora}}
Pasajeros: {{pasajeros}}
Total: {{precio}}

Cliente: {{nombre_cliente}}
Teléfono: {{telefono_cliente}}
Código: {{codigo}}

Responda 1 para confirmar disponibilidad, 2 para rechazar.""",

    'customer_waiting': """Estimado/a {{nombre_cliente}},

Gracias por su interés en {{experiencia}} para el {{fecha}} a las {{hora}}. Estamos gestionando la disponibilidad con el operador y le mantendremos informado(a). Número de referencia: {{codigo}}.""",

    'customer_confirmation': """Estimado/a {{nombre_cliente}},

Su reserva ha sido confirmada.

Experiencia: {{experiencia}}
Fecha: {{fecha}}
Hora: {{hora}}
Pasajeros: {{pasajeros}}
Total: {{precio}}

Codigo: {{codigo}}
{{link_pago_mensaje}}""",

    'customer_availability_confirmed': """Estimado/a {{nombre_cliente}},

El operador confirmó disponibilidad para su solicitud.

{{pasos_siguientes}}""",

    'customer_rejection': """Estimado/a {{nombre_cliente}},

Lamentamos informarle que no hay disponibilidad para {{experiencia}} el {{fecha}} a las {{hora}}.

Desea intentar con otro horario?""",

    'payment_link': """Estimado/a {{nombre_cliente}},

Para completar su reserva puede realizar el pago en el siguiente enlace:
{{link_pago}}

Monto a pagar: {{precio}}.
El enlace expira en 30 minutos. Referencia: {{codigo}}.""",

    'payment_confirmed': """Estimado/a {{nombre_cliente}},

Hemos recibido su pago correctamente.

Experiencia: {{experiencia}}
Fecha: {{fecha}}
Hora: {{hora}}
Total pagado: {{precio}}

Su comprobante llegara en unos momentos.
Codigo: {{codigo}}""",

    'customer_confirm_free': """Estimado/a {{nombre_cliente}},

Hay disponibilidad para su reserva. Como la actividad no tiene costo, solo debe responder SI para confirmarla. Referencia: {{codigo}}.""",

    'ticket_info': """Comprobante de reserva

Experiencia: {{experiencia}}
Fecha: {{fecha}}
Hora: {{hora}}
Punto de encuentro: {{punto_encuentro}}

Pasajeros: {{pasajeros}}
Codigo: {{codigo}}

{{instrucciones}}""",

    'reminder': """Recordatorio

Hola {{contacto}},

Reserva pendiente de confirmacion:
Experiencia: {{experiencia}}
Fecha: {{fecha}}
Hora: {{hora}}
Codigo: {{codigo}}

Responda 1 para confirmar disponibilidad, 2 para rechazar.""",
}
