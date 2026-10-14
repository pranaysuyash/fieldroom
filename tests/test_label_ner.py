from pdf_field_lab.label_ner import entity_types, extract_label_entities


def test_label_intent_entities_are_stable_and_typed():
    entities = extract_label_entities("Authorized signature and email address:")

    assert "SIGNATURE_FIELD" in entity_types("Authorized signature and email address:")
    assert "EMAIL_FIELD" in entity_types("Authorized signature and email address:")
    assert all(entity["source"] == "label-rule" for entity in entities)


def test_notes_does_not_trigger_choice_entity_from_short_no_token():
    assert "CHOICE_FIELD" not in entity_types("Travel notes:")
    assert "TEXT_AREA_FIELD" in entity_types("Travel notes and additional details:")


def test_passport_photo_is_photo_intent_not_identifier_intent():
    assert "PHOTO_FIELD" in entity_types("Passport photo:")
    assert "IDENTIFIER_FIELD" not in entity_types("Passport photo:")
    assert "IDENTIFIER_FIELD" in entity_types("Passport number:")
