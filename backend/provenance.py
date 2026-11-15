"""Disclosures describing SI-assisted code and the provenance of app data."""

SI_PROVENANCE = {
    "disclosure": "This application was created with SI (synthetic intelligence) assistance.",
    "code": {
        "origin": "SI-generated and SI-assisted software",
        "review_note": "Recommendations and risk scores are rule-based screening aids and require local validation.",
    },
    "derived_outputs": {
        "origin": "Calculated by Orbit Crop algorithms, with SI-assisted implementation",
        "examples": ["crop suitability scores", "rotation suggestions", "hazard screening levels"],
    },
    "external_data": {
        "origin": "Fetched from and attributed to the providers named in each response",
        "si_generated": False,
        "note": "NASA, Open-Meteo, SoilGrids, and other provider observations or model products are not represented as SI-generated.",
    },
    "media": {
        "generated_images_or_video": False,
        "generated_audio": False,
        "note": "The app currently contains no SI-generated images, video, or audio.",
    },
}
