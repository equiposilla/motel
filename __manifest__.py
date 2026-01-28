# __manifest__.py
{
    "name": "Motel",
    "author": "Equipo silla",
    "version": "1.2.0",
    "category": "Website",
    "summary": "Website de disponibilidad y reservas de motel con precios automáticos.",
    "depends": [
        "base",     
        "website",  
        "sale",
        "payment",     
        # "account", # para generar facturas desde la SO una vez implementado el pago
        # "mail",    # implemntado el pago y la facturación enviar facturas por email
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",     # folio reference RES-000001...
        "data/demo.xml",
        "views/backend_views.xml",
        "views/templates.xml",
        
    ],
    "assets": {
        
        "web.assets_frontend_minimal": [
            "motel/static/src/js/motel_availability.js",
            "motel/static/src/css/motel_availability.css",
        ],
        
        "web.assets_frontend": [
            "motel/static/src/js/motel_availability.js",
            "motel/static/src/css/motel_availability.css",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
