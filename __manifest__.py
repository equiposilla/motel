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
        "data/menu.xml",
        "views/backend_views.xml",
        "views/templates.xml",
        
    ],
    "assets": {
    "web.assets_backend": [
        
        "motel/static/lib/leaflet/leaflet.css",
        "motel/static/lib/leaflet/leaflet.js",

        "motel/static/src/css/geo_picker_field.css",
        "motel/static/src/xml/geo_picker_field.xml",
        "motel/static/src/js/geo_picker_field.js",
    ],

    "web.assets_frontend": [
        "motel/static/src/css/motel_availability.css",
        "motel/static/src/js/motel_availability.js",
        "motel/static/lib/leaflet/leaflet.css",
        "motel/static/lib/leaflet.markercluster/MarkerCluster.css",
        "motel/static/lib/leaflet.markercluster/MarkerCluster.Default.css",

        "motel/static/lib/leaflet/leaflet.js",
        "motel/static/lib/leaflet.markercluster/leaflet.markercluster.js",

        "motel/static/src/css/motel_map.css",
        "motel/static/src/js/motel_map.js",
    ],
        "web.assets_frontend_minimal": [
        "motel/static/src/css/motel_availability.css",
        "motel/static/src/js/motel_availability.js",
        "motel/static/lib/leaflet/leaflet.css",
        "motel/static/lib/leaflet.markercluster/MarkerCluster.css",
        "motel/static/lib/leaflet.markercluster/MarkerCluster.Default.css",

        "motel/static/lib/leaflet/leaflet.js",
        "motel/static/lib/leaflet.markercluster/leaflet.markercluster.js",

        "motel/static/src/css/motel_map.css",
        "motel/static/src/js/motel_map.js",
    ],
    },

    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
