# __manifest__.py
{
    "name": "Motel Availability (HU-01 + HU-02)",
    "version": "1.1.0",
    "category": "Website",
    "depends": ["website", "sale"],
    "data": [
        "data/demo.xml",
        "security/ir.model.access.csv",
        "views/templates.xml",
    ],
    "assets": {
        # Tu /motels usa frontend_minimal normalmente
        "web.assets_frontend_minimal": [
            "motel_availability/static/src/js/motel_availability.js",
        ],
    },
    "application": False,
    "license": "LGPL-3",
}
