# __manifest__.py
{
    "name": "Motel Availability (HU-01)",
    "version": "1.0.0",
    "category": "Website",
    "depends": ["website"],
    "data": [
        "data/demo.xml",
        "security/ir.model.access.csv",
        "views/templates.xml"
    ],
    "assets": {
        "web.assets_frontend_minimal": [
            "motel_availability/static/src/js/motel_availability.js",
        ],
    },
    "application": False,
    "license": "LGPL-3",
}
