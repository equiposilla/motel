# __manifest__.py
{
<<<<<<< HEAD
    "name": "Motel Availability (HU-01 + HU-02)",
    "version": "1.1.0",
    "category": "Website",
    "depends": ["website", "sale"],
=======
    "name": "Motel Availability (HU-01 + HU-02 + HU-04)",
    "author": "Equipo silla",
    "version": "1.2.0",
    "category": "Website",
    "summary": "Website de disponibilidad y reservas de motel con precios automáticos.",
    "depends": [
        "base",     
        "website",  
        "sale",     
        # "account", # para generar facturas desde la SO una vez implementado el pago
        # "mail",    # implemntado el pago y la facturación enviar facturas por email
    ],
>>>>>>> HU-4
    "data": [
        "security/ir.model.access.csv",
<<<<<<< HEAD
        "views/templates.xml",
    ],
"assets": {
    "web.assets_frontend": [
        "motel_availability/static/src/js/motel_availability.js",
        "motel_availability/static/src/css/motel_availability.css",
    ],
    "web.assets_frontend_minimal": [
        "motel_availability/static/src/js/motel_availability.js",
        "motel_availability/static/src/css/motel_availability.css",
    ],
},
=======
        "data/sequence.xml",     # folio reference RES-000001...
        "data/demo.xml",
        "views/templates.xml",   # incluye qweb + vistas backend que agregamos
    ],
    "assets": {
        # Tu /motels suele usar frontend_minimal
        "web.assets_frontend_minimal": [
            "motel_availability/static/src/js/motel_availability.js",
            "motel_availability/static/src/css/motel_availability.css",
        ],
        # Por si alguna página cae en el bundle normal
        "web.assets_frontend": [
            "motel_availability/static/src/js/motel_availability.js",
            "motel_availability/static/src/css/motel_availability.css",
        ],
    },
    "installable": True,
>>>>>>> HU-4
    "application": False,
    "license": "LGPL-3",
}
